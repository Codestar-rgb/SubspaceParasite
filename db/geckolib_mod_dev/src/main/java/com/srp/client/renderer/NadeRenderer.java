package com.srp.client.renderer;

import com.srp.client.model.NadeModel;
import com.srp.entity.NadeEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class NadeRenderer extends GeoEntityRenderer<NadeEntity> {

    public NadeRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new NadeModel());
    }
}
