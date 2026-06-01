package com.srp.client.renderer;

import com.srp.client.model.ElviaModel;
import com.srp.entity.ElviaEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class ElviaRenderer extends GeoEntityRenderer<ElviaEntity> {

    public ElviaRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new ElviaModel());
    }
}
