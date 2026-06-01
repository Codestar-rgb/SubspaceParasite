package com.srp.client.renderer;

import com.srp.client.model.DeterrentLeemModel;
import com.srp.entity.DeterrentLeemEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class DeterrentLeemRenderer extends GeoEntityRenderer<DeterrentLeemEntity> {

    public DeterrentLeemRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new DeterrentLeemModel());
    }
}
